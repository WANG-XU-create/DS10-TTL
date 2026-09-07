#!/bin/bash
# 一键启动 DS10 三跳中继「全自动」栈:
#   3 个驱动 (一主两从) + 从机1 应答器 (route_map 自动决定 dst) + 主机中继。
#
# 起完后, 用 ros2 topic pub 触发一次事务即可, 无需人工介入:
#   ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'temp=25'}"
#
#   主机  /dev/ttyUSB0  ->  /master/tx   /master/rx        (中继)
#   从机1 /dev/ttyUSB1  ->  /slave1/tx   /slave1/rx   站号1 (应答器)
#   从机2 /dev/ttyUSB2  ->  /slave2/tx   /slave2/rx   站号2 (转发目标)
#
# 注意: 本脚本跑的是「自动应答器」。若要「人工打回复」的交互测试, 不要用本脚本,
# 改用 ./start_ds10.sh (只起驱动) + 两个交互脚本, 见 README「交互式手动测试」。
# 两种应答器同时跑会造成一个请求两份回复。
#
# 用法:
#   ./start_relay.sh                                  # 默认路由 temp->站号2, 其它不转发
#   ROUTE_MAP="temp:2,humid:2" ./start_relay.sh       # 自定义路由表
#   DEFAULT_DST=2 ./start_relay.sh                    # 无命中时也转发到站号2
#   ./start_relay.sh -b 230400                        # 改波特率

cd "$(dirname "$0")"

MASTER_PORT="${MASTER_PORT:-/dev/ttyUSB0}"
SLAVE1_PORT="${SLAVE1_PORT:-/dev/ttyUSB1}"
SLAVE2_PORT="${SLAVE2_PORT:-/dev/ttyUSB2}"
BAUD="${BAUD:-115200}"
# 只有两台从机 (站号1=应答器, 站号2=转发目标), 故默认把 temp 路由到站号2、
# 其它不转发。有更多从机时按硬件扩展, 如 ROUTE_MAP="temp:2,humid:3"。
ROUTE_MAP="${ROUTE_MAP:-temp:2}"
DEFAULT_DST="${DEFAULT_DST:-0}"
SLAVE1_ID="${SLAVE1_ID:-1}"
TIMEOUT_MS="${TIMEOUT_MS:-1500}"

while getopts "b:h" opt; do
  case "$opt" in
    b) BAUD="$OPTARG" ;;
    h) sed -n '2,24p' "$0"; exit 0 ;;
    *) exit 2 ;;
  esac
done

# 只杀本栈进程, [d]/[r] 写法避免匹配到本脚本自身的命令行。残留的应答器/中继
# 会与新一轮并存造成重复应答 (一个请求多份回复), 一并清掉。
pkill -f "[d]s10_node" 2>/dev/null
pkill -f "[r]elay_node" 2>/dev/null
pkill -f "[d]s10_relay_master.py" 2>/dev/null
pkill -f "[d]s10_relay_responder.py" 2>/dev/null
pkill -f "[d]s10_relay_responder_interactive.py" 2>/dev/null
sleep 1

if [ ! -f install/setup.bash ]; then
  echo "错误: 未找到 install/setup.bash, 请先在 $(pwd) 执行 colcon build" >&2
  exit 1
fi

source /opt/ros/humble/setup.bash
source install/setup.bash

# 逐口检查设备存在与可读写, 早失败好过启动后静默无数据
for p in "$MASTER_PORT" "$SLAVE1_PORT" "$SLAVE2_PORT"; do
  if [ ! -e "$p" ]; then
    echo "错误: 串口不存在: $p" >&2
    exit 1
  fi
  if [ ! -r "$p" ] || [ ! -w "$p" ]; then
    echo "错误: 无权访问 $p (需加入 dialout 组: sudo usermod -a -G dialout $USER, 然后重新登录)" >&2
    exit 1
  fi
done

rm -f /tmp/ds10_master.log /tmp/ds10_slave1.log /tmp/ds10_slave2.log \
      /tmp/ds10_responder.log /tmp/ds10_relay.log

PIDS=()

start_driver() {
  local name="$1" port="$2" role="$3" station="$4" ns="$5" log="$6"
  echo "启动 ${name}: ${port} (${role}, station_id=${station}) -> /${ns}/tx  /${ns}/rx"
  ros2 run ds10_driver ds10_node --ros-args \
    -r __node:="ds10_${ns}" \
    -p port:="$port" \
    -p baud:="$BAUD" \
    -p role:="$role" \
    -p station_id:="$station" \
    -p tx_topic:="/${ns}/tx" \
    -p rx_topic:="/${ns}/rx" \
    > "$log" 2>&1 &
  PIDS+=($!)
}

echo "=========================================="
echo "启动 DS10 三跳中继全自动栈 (波特率 ${BAUD}, 8N1)"
echo "=========================================="
start_driver "主机 " "$MASTER_PORT" master 0 master /tmp/ds10_master.log
start_driver "从机1" "$SLAVE1_PORT" slave  1 slave1 /tmp/ds10_slave1.log
start_driver "从机2" "$SLAVE2_PORT" slave  2 slave2 /tmp/ds10_slave2.log

sleep 3

# 确认三个驱动都活着且串口真的打开了, 再起上层节点
echo ""
failed=0
for i in "${!PIDS[@]}"; do
  if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
    echo "错误: 第 $((i+1)) 个驱动启动后退出, 见日志" >&2
    failed=1
  fi
done
for log in /tmp/ds10_master.log /tmp/ds10_slave1.log /tmp/ds10_slave2.log; do
  if grep -q "serial connected" "$log" 2>/dev/null; then
    echo "  OK   $(grep -o 'serial connected: .*' "$log" | tail -1)"
  else
    echo "  失败 $log 未见 'serial connected'" >&2
    tail -3 "$log" >&2
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  echo ""
  echo "驱动未完全就绪, 正在清理..." >&2
  kill "${PIDS[@]}" 2>/dev/null
  exit 1
fi

# 上层节点不碰串口, 起完确认进程存活即可
echo ""
echo "启动 从机1 应答器 (route_map=\"${ROUTE_MAP}\" default_dst=${DEFAULT_DST})"
ros2 run ds10_relay relay_node --ros-args \
  -r __node:=ds10_responder \
  -p role:=responder \
  -p route_map:="$ROUTE_MAP" \
  -p default_dst:="$DEFAULT_DST" \
  -p tx_topic:=/slave1/tx \
  -p rx_topic:=/slave1/rx \
  > /tmp/ds10_responder.log 2>&1 &
PIDS+=($!)

echo "启动 主机中继 (slave1_id=${SLAVE1_ID} timeout=${TIMEOUT_MS}ms)"
ros2 run ds10_relay relay_node --ros-args \
  -r __node:=ds10_relay \
  -p role:=relay \
  -p slave1_id:="$SLAVE1_ID" \
  -p timeout_ms:="$TIMEOUT_MS" \
  -p tx_topic:=/master/tx \
  -p rx_topic:=/master/rx \
  > /tmp/ds10_relay.log 2>&1 &
PIDS+=($!)

sleep 3

for log in /tmp/ds10_responder.log /tmp/ds10_relay.log; do
  if ! grep -qE "responder:|relay:" "$log" 2>/dev/null; then
    echo "  失败 $log 未见启动横幅" >&2
    tail -3 "$log" >&2
    failed=1
  fi
done
if [ "$failed" -ne 0 ]; then
  echo "上层节点启动异常, 正在清理..." >&2
  kill "${PIDS[@]}" 2>/dev/null
  exit 1
fi

cat <<EOF

==========================================
三跳中继全自动栈已就绪
==========================================
链路: /ds10_relay/trigger -> 从机1 应答(按 route_map 选 dst) -> 转发给 dst

触发一次事务 (另开终端, 先 source):
  source /opt/ros/humble/setup.bash && source install/setup.bash
  ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'temp=25.3'}"
  ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'other'}"   # 不命中 -> 不转发

观察:
  ros2 topic echo /ds10_relay/stats     # 中继计数
  ros2 topic echo /slave2/rx            # 转发目标实收
  tail -f /tmp/ds10_relay.log           # 中继日志
  tail -f /tmp/ds10_responder.log       # 应答器日志

当前路由: ${ROUTE_MAP}  (无命中时 default_dst=${DEFAULT_DST}$([ "$DEFAULT_DST" = "0" ] && echo ' 即不转发'))

人工打回复的交互测试请勿用本脚本 (自动应答器会抢答), 见 README「交互式手动测试」。
按 Ctrl+C 停止所有节点
==========================================
EOF

trap 'echo ""; echo "正在停止..."; kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; echo "已停止"; exit 0' SIGINT SIGTERM

wait
