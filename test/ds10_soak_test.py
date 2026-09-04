#!/usr/bin/env python3
"""DS10 一主两从长时间收发稳定性测试 —— 检测长跑是否丢数据。

驱动节点由 start_ds10.sh 启动, 本脚本直连驱动 topic:
  /master/tx  /master/rx    主机
  /slave1/tx  /slave1/rx    从机1 (station_id=1)
  /slave2/tx  /slave2/rx    从机2 (station_id=2)

## 固定数据内容

  主机  -> 从机   "主机123456789"
  从机1 -> 主机   "从机1：123456789"
  从机2 -> 主机   "从机2：123456789"

## 一个循环 = 四轮

  第一轮  主机 -> 从机1  +  主机 -> 从机2      (同时)
  第二轮  从机1 -> 主机  +  从机2 -> 主机      (同时)
  第三轮  主机 -> 从机1  +  从机2 -> 主机      (同时, 双向交叉)
  第四轮  主机 -> 从机2  +  从机1 -> 主机      (同时, 第三轮的镜像)

每轮发完等 --gap 秒收齐再进入下一轮, 所以每轮的收发是干净配对的,
不会出现上一轮的在途数据混进本轮统计。

## 丢包如何判定

每轮每条链路只发 1 帧, 收端按"到达的 topic + 内容"归属:
  从机1/rx 收到主机文本  -> 主机->从机1 这条链路到达
  主机/rx  收到且 station_id=1 -> 从机1->主机 到达 (驱动填的来源站号)
应到未到即为丢失; 内容不符记为损坏; 到了不该到的地方记为错投。

用法:
  source /opt/ros/humble/setup.bash && source install/setup.bash

  # 默认循环 10 次 (共 40 轮, 80 帧)
  python3 test/ds10_soak_test.py

  # 长跑 500 次循环
  python3 test/ds10_soak_test.py -n 500

  # 加大每轮间隔到 2s, 拉长总时长
  python3 test/ds10_soak_test.py -n 1000 --gap 2.0

  # 在文本尾部附加序号, 便于精确追踪某一帧 (会改变数据内容)
  python3 test/ds10_soak_test.py -n 100 --seq

  # 复现 DS10 设备背靠背丢包: 0ms 间隔, 第一轮从机2 必丢
  python3 test/ds10_soak_test.py -n 5 --intra-gap 0.0

中途 Ctrl+C 会打印已完成部分的统计。
"""

import argparse
import statistics
import sys
import threading
import time
from collections import defaultdict

try:
    import rclpy
    from rclpy.node import Node

    from ds10_interfaces.msg import Frame
except ModuleNotFoundError as e:
    sys.exit(
        f"错误: 无法导入 {e.name} —— ROS 2 环境未加载。\n"
        "请先在本终端执行:\n"
        "  source /opt/ros/humble/setup.bash\n"
        "  source install/setup.bash\n"
        "(需在 ~/DS10_Modbus 目录下, 且已 colcon build)"
    )

FUNC_TEXT = 0x10          # 与交互式/监控脚本一致的文本功能码

# 用户指定的固定数据内容
TEXT_MASTER = "主机123456789"
TEXT_SLAVE1 = "从机1：123456789"
TEXT_SLAVE2 = "从机2：123456789"

# 链路定义: key -> (可读名, 发送方 topic, 目标站号, 文本, 收件处)
#   目标站号: 主机发送时是路由目标; 从机发送时驱动会用启动参数覆盖, 填 0 即可
M1 = "主机->从机1"
M2 = "主机->从机2"
S1 = "从机1->主机"
S2 = "从机2->主机"

LINKS = {
    M1: {"topic": "/master/tx", "station": 1, "text": TEXT_MASTER, "arrive": "从机1"},
    M2: {"topic": "/master/tx", "station": 2, "text": TEXT_MASTER, "arrive": "从机2"},
    S1: {"topic": "/slave1/tx", "station": 0, "text": TEXT_SLAVE1, "arrive": "主机"},
    S2: {"topic": "/slave2/tx", "station": 0, "text": TEXT_SLAVE2, "arrive": "主机"},
}

# 四轮, 每轮同时发送的链路
ROUNDS = [
    ("第一轮  主机同时发给两个从机", [M1, M2]),
    ("第二轮  两个从机同时发给主机", [S1, S2]),
    ("第三轮  主机->从机1 与 从机2->主机", [M1, S2]),
    ("第四轮  主机->从机2 与 从机1->主机", [M2, S1]),
]


def decode(data):
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        return None


class SoakTester(Node):

    def __init__(self, append_seq=False):
        super().__init__("ds10_soak_tester")
        self._append_seq = append_seq

        # 主机两条下行链路共用 /master/tx, 靠 station_id 区分目标
        self._master_tx = self.create_publisher(Frame, "/master/tx", 50)
        self._slave1_tx = self.create_publisher(Frame, "/slave1/tx", 50)
        self._slave2_tx = self.create_publisher(Frame, "/slave2/tx", 50)
        self._pubs = {
            "/master/tx": self._master_tx,
            "/slave1/tx": self._slave1_tx,
            "/slave2/tx": self._slave2_tx,
        }

        self.create_subscription(Frame, "/slave1/rx", self._on_slave1_rx, 50)
        self.create_subscription(Frame, "/slave2/rx", self._on_slave2_rx, 50)
        self.create_subscription(Frame, "/master/rx", self._on_master_rx, 50)

        self._lock = threading.Lock()
        # 本轮收件箱: 链路名 -> [(文本, 到达时刻)]
        self._inbox = defaultdict(list)
        self._corrupted = []      # [(到达处, 原始内容摘要)]
        self._unexpected = []     # [(链路, 到达处)] 到了不该到的地方
        self._send_at = {}        # 链路 -> 发送时刻
        self._expected = set()    # 本轮应到的链路

    # ---- 接收: 按 topic + 内容归属到链路 ----

    def _classify(self, msg, arrived_at):
        text = decode(msg.data)
        now = time.monotonic()

        if text is None:
            with self._lock:
                self._corrupted.append((arrived_at, "hex:" + bytes(msg.data).hex(" ")[:40]))
            return

        # 去掉可能附加的 "#序号" 后缀再比对
        base = text.split("#", 1)[0] if self._append_seq else text

        if arrived_at == "从机1":
            link = M1 if base == TEXT_MASTER else None
        elif arrived_at == "从机2":
            link = M2 if base == TEXT_MASTER else None
        else:  # 主机: 用驱动填的来源站号区分是哪个从机发的
            if msg.station_id == 1 and base == TEXT_SLAVE1:
                link = S1
            elif msg.station_id == 2 and base == TEXT_SLAVE2:
                link = S2
            else:
                link = None

        with self._lock:
            if link is None:
                self._corrupted.append((arrived_at, repr(text[:30])))
                return
            if link not in self._expected:
                # 本轮没发这条链路却收到了 —— 站号映射错或上一轮迟到
                self._unexpected.append((link, arrived_at))
                return
            self._inbox[link].append((text, now))

    def _on_slave1_rx(self, msg):
        self._classify(msg, "从机1")

    def _on_slave2_rx(self, msg):
        self._classify(msg, "从机2")

    def _on_master_rx(self, msg):
        self._classify(msg, "主机")

    # ---- 发送 ----

    def begin_round(self, links):
        with self._lock:
            self._inbox.clear()
            self._send_at.clear()
            self._expected = set(links)

    def send(self, link, seq):
        spec = LINKS[link]
        text = spec["text"]
        if self._append_seq:
            text = f"{text}#{seq}"

        msg = Frame()
        msg.station_id = spec["station"]
        msg.function_code = FUNC_TEXT
        msg.data = list(text.encode("utf-8"))
        msg.tx_seq = seq          # 本地字段, 不上无线; 仅供监控脚本显示
        with self._lock:
            self._send_at[link] = time.monotonic()
        self._pubs[spec["topic"]].publish(msg)

    def collect(self):
        """返回本轮 (每条链路收到几帧, 延迟ms, 损坏, 错投)。"""
        with self._lock:
            got = {k: len(v) for k, v in self._inbox.items()}
            lat = {}
            for link, items in self._inbox.items():
                sent = self._send_at.get(link)
                if sent is not None and items:
                    lat[link] = (items[0][1] - sent) * 1000.0
            corrupted = list(self._corrupted)
            unexpected = list(self._unexpected)
            self._corrupted.clear()
            self._unexpected.clear()
            return got, lat, corrupted, unexpected


def main():
    p = argparse.ArgumentParser(
        description="DS10 一主两从长时间收发稳定性测试(固定数据, 四轮循环)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-n", "--iterations", type=int, default=10,
                   help="四轮循环重复次数 (默认 10)")
    p.add_argument("--gap", type=float, default=1.0,
                   help="每轮发完后等待收齐的秒数 (默认 1.0)")
    p.add_argument("--intra-gap", type=float, default=0.01,
                   help="同一轮内两帧之间的间隔秒 (默认 0.01)。"
                        "实测 DS10 主机背靠背连发两帧(0ms 间隔)时第二帧会被"
                        "内部丢弃, >=5ms 即可 100%% 到达; 设为 0 可复现该问题")
    p.add_argument("--pause", type=float, default=0.0,
                   help="每个循环之间额外停顿秒数 (默认 0)")
    p.add_argument("--seq", action="store_true",
                   help="在文本尾部附加 #序号 (会改变数据内容, 便于精确追踪)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="只在出错和汇总时输出, 适合长跑")
    args = p.parse_args()

    if args.iterations < 1:
        p.error("循环次数必须 >= 1")

    rclpy.init()
    node = SoakTester(append_seq=args.seq)
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()

    total_rounds = args.iterations * len(ROUNDS)
    total_frames = total_rounds * 2
    est = args.iterations * (len(ROUNDS) * args.gap + args.pause)

    print("=" * 74)
    print("DS10 一主两从长时间收发稳定性测试")
    print("=" * 74)
    print(f"  循环次数: {args.iterations}   总轮数: {total_rounds}   总帧数: {total_frames}")
    print(f"  每轮等待: {args.gap}s   预计耗时: {est / 60:.1f} 分钟")
    print(f"  轮内两帧间隔: {args.intra_gap * 1000:.0f}ms"
          + ("   (0ms 会触发 DS10 设备侧丢帧)" if args.intra_gap <= 0 else ""))
    print(f"  数据内容: 主机={TEXT_MASTER!r}")
    print(f"            从机1={TEXT_SLAVE1!r}")
    print(f"            从机2={TEXT_SLAVE2!r}")
    if args.seq:
        print("  已启用 --seq: 文本尾部附加 #序号")
    print()
    print("等待 ROS 2 连接建立...")
    time.sleep(2)

    if node.count_subscribers("/master/tx") == 0:
        print("\n警告: /master/tx 无订阅者 —— 驱动节点似乎未运行。")
        print("      请先在终端1执行 ./start_ds10.sh\n")

    # 累计统计
    sent_cnt = defaultdict(int)
    recv_cnt = defaultdict(int)
    lat_all = defaultdict(list)
    round_lost = defaultdict(int)         # 轮次索引 -> 丢失帧数
    corrupted_all = []
    unexpected_all = []
    lost_detail = []                      # [(循环号, 轮名, 链路)]
    seq_no = 0
    done_rounds = 0

    t_start = time.monotonic()
    try:
        for it in range(1, args.iterations + 1):
            for r_idx, (r_name, links) in enumerate(ROUNDS):
                node.begin_round(links)
                seq_no += 1

                # 两帧之间留 --intra-gap 间隔: DS10 主机背靠背收两帧时会丢第二帧
                for i, link in enumerate(links):
                    if i and args.intra_gap > 0:
                        time.sleep(args.intra_gap)
                    node.send(link, seq_no)
                    sent_cnt[link] += 1

                time.sleep(args.gap)
                got, lat, corrupted, unexpected = node.collect()
                done_rounds += 1

                lost_here = []
                for link in links:
                    n = got.get(link, 0)
                    recv_cnt[link] += min(n, 1)
                    if link in lat:
                        lat_all[link].append(lat[link])
                    if n == 0:
                        lost_here.append(link)
                        round_lost[r_idx] += 1
                        lost_detail.append((it, r_name, link))

                corrupted_all.extend(corrupted)
                unexpected_all.extend(unexpected)

                if lost_here or corrupted or unexpected:
                    print(f"  [循环{it} {r_name}]", end="")
                    if lost_here:
                        print(f" 丢失: {', '.join(lost_here)}", end="")
                    if corrupted:
                        print(f" 损坏×{len(corrupted)}", end="")
                    if unexpected:
                        print(f" 错投×{len(unexpected)}", end="")
                    print()
                elif not args.quiet:
                    lat_str = "/".join(f"{lat.get(l, 0):.0f}" for l in links)
                    print(f"  [循环{it} {r_name}] OK  延迟 {lat_str} ms")

            if args.pause:
                time.sleep(args.pause)

            # 长跑时每 20 个循环给一次进度小结
            if args.iterations >= 20 and it % 20 == 0:
                s = sum(sent_cnt.values())
                r = sum(recv_cnt.values())
                el = time.monotonic() - t_start
                print(f"  --- 进度 {it}/{args.iterations} 循环, "
                      f"已发 {s} 收 {r}, 丢失 {s - r}, 用时 {el / 60:.1f} 分钟 ---")

    except KeyboardInterrupt:
        print(f"\n\n已中断 (完成 {done_rounds}/{total_rounds} 轮)")

    elapsed = time.monotonic() - t_start

    # ---- 汇总 ----
    print()
    print("=" * 74)
    print("测试汇总")
    print("=" * 74)
    print(f"  实际用时 {elapsed / 60:.1f} 分钟, 完成 {done_rounds}/{total_rounds} 轮")
    print()
    print("  链路            发送   收到   丢失   丢失率    延迟 min/avg/max (ms)")
    print("  " + "-" * 70)
    total_s = total_r = 0
    for link in (M1, M2, S1, S2):
        s = sent_cnt[link]
        r = recv_cnt[link]
        if s == 0:
            continue
        lost = s - r
        lat = lat_all[link]
        lat_str = (f"{min(lat):.0f}/{statistics.mean(lat):.0f}/{max(lat):.0f}"
                   if lat else "—")
        print(f"  {link:<14} {s:>5}  {r:>5}  {lost:>5}  {100.0 * lost / s:>6.2f}%    {lat_str}")
        total_s += s
        total_r += r
    print("  " + "-" * 70)
    total_lost = total_s - total_r
    pct = 100.0 * total_lost / total_s if total_s else 0.0
    print(f"  {'合计':<14} {total_s:>5}  {total_r:>5}  {total_lost:>5}  {pct:>6.2f}%")

    if any(round_lost.values()):
        print()
        print("  按轮次分布丢失:")
        for r_idx, (r_name, _) in enumerate(ROUNDS):
            n = round_lost.get(r_idx, 0)
            if n:
                print(f"    {r_name}: 丢失 {n} 帧")

    if lost_detail:
        print()
        print(f"  丢失明细(前 15 条, 共 {len(lost_detail)} 条):")
        for it, r_name, link in lost_detail[:15]:
            print(f"    循环{it}  {r_name}  {link}")

    if corrupted_all:
        print()
        print(f"  ⚠ 内容损坏 {len(corrupted_all)} 帧(前 5 条):")
        for where, sample in corrupted_all[:5]:
            print(f"    到达 {where}: {sample}")

    if unexpected_all:
        print()
        print(f"  ⚠ 错投 {len(unexpected_all)} 帧 —— 本轮未发该链路却收到了。")
        print("    可能是 DS10 通道站号映射与串口对应关系不符, 或上一轮数据迟到。")
        agg = defaultdict(int)
        for link, where in unexpected_all:
            agg[(link, where)] += 1
        for (link, where), n in sorted(agg.items(), key=lambda x: -x[1])[:5]:
            print(f"    {link} 出现在 {where} ×{n}")

    print()
    if total_s == 0:
        print("  未发送任何数据。")
    elif total_lost == 0 and not corrupted_all and not unexpected_all:
        print(f"  判定: 全部到达, 零丢失 —— 长跑 {done_rounds} 轮未见数据丢失")
    elif pct < 1:
        print(f"  判定: 轻微丢失 {pct:.2f}% —— 建议加大 --gap 或延长测试确认是否偶发")
    else:
        print(f"  判定: 丢失 {pct:.2f}% —— 存在稳定性问题, 见上方明细")

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
