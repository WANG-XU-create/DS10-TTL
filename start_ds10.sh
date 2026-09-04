#!/bin/bash
# 一键启动 DS10 驱动节点(一主两从)。
#
# 协议桥已移除, 应用层直接对接驱动 topic。三个节点用 tx_topic/rx_topic
# 参数显式指定绝对 topic 名, 不依赖命名空间解析:
#
#   主机  /dev/ttyUSB0  ->  /master/tx   /master/rx
#   从机1 /dev/ttyUSB1  ->  /slave1/tx   /slave1/rx   station_id=1
#   从机2 /dev/ttyUSB2  ->  /slave2/tx   /slave2/rx   station_id=2
#
# 用法:
#   ./start_ds10.sh                       # 默认三口 115200
#   ./start_ds10.sh -b 230400             # 改波特率
#   MASTER_PORT=/dev/ttyUSB3 ./start_ds10.sh

cd "$(dirname "$0")"

MASTER_PORT="${MASTER_PORT:-/dev/ttyUSB0}"
SLAVE1_PORT="${SLAVE1_PORT:-/dev/ttyUSB1}"
SLAVE2_PORT="${SLAVE2_PORT:-/dev/ttyUSB2}"
BAUD="${BAUD:-115200}"

while getopts "b:h" opt; do
  case "$opt" in
    b) BAUD="$OPTARG" ;;
    h) sed -n '2,16p' "$0"; exit 0 ;;
    *) exit 2 ;;
  esac
done

# 只杀驱动进程, [d] 写法避免匹配到本脚本自身的命令行
pkill -f "[d]s10_node" 2>/dev/null
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

rm -f /tmp/ds10_master.log /tmp/ds10_slave1.log /tmp/ds10_slave2.log

PIDS=()

start_node() {
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
echo "启动 DS10 驱动节点 (波特率 ${BAUD}, 8N1)"
echo "=========================================="
start_node "主机 " "$MASTER_PORT" master 0 master /tmp/ds10_master.log
start_node "从机1" "$SLAVE1_PORT" slave  1 slave1 /tmp/ds10_slave1.log
start_node "从机2" "$SLAVE2_PORT" slave  2 slave2 /tmp/ds10_slave2.log

sleep 3

# 确认三个节点都活着, 并且串口真的打开了
echo ""
failed=0
for i in "${!PIDS[@]}"; do
  if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
    echo "错误: 第 $((i+1)) 个节点启动后退出, 见日志" >&2
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
  echo "启动未完全成功, 正在清理..." >&2
  kill "${PIDS[@]}" 2>/dev/null
  exit 1
fi

cat <<EOF

==========================================
三个驱动节点已就绪
==========================================
Topic:
  主机   /master/tx  (发送)   /master/rx  (接收, station_id=来源从机)
  从机1  /slave1/tx  (发送)   /slave1/rx  (接收, station_id=0 表示来自主机)
  从机2  /slave2/tx  (发送)   /slave2/rx  (接收, station_id=0 表示来自主机)

下一步 (终端2/终端3 都需先加载 ROS 环境):
  source /opt/ros/humble/setup.bash && source install/setup.bash

  终端2  python3 test/ds10_interactive_test.py    # 手动输入数据测试
  终端3  python3 test/ds10_monitor.py -v          # 实时监控收发

日志:
  tail -f /tmp/ds10_master.log
  tail -f /tmp/ds10_slave1.log
  tail -f /tmp/ds10_slave2.log

按 Ctrl+C 停止所有节点
==========================================
EOF

trap 'echo ""; echo "正在停止..."; kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; echo "已停止"; exit 0' SIGINT SIGTERM

wait
