// Copyright 2026 wangxu
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "ds10_driver/serial_port.hpp"

#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>

namespace ds10_driver
{

namespace
{
constexpr std::size_t kReadChunk = 4096;
}  // namespace

SerialPort::~SerialPort()
{
  close();
}

int SerialPort::baud_constant(int baud)
{
  switch (baud) {
    case 9600: return B9600;
    case 19200: return B19200;
    case 38400: return B38400;
    case 57600: return B57600;
    case 115200: return B115200;
    case 230400: return B230400;
    case 460800: return B460800;
    case 921600: return B921600;
    default: return -1;
  }
}

bool SerialPort::open(const std::string & device, int baud)
{
  close();
  const int speed = baud_constant(baud);
  if (speed < 0) {
    last_error_ = "unsupported baud rate: " + std::to_string(baud);
    return false;
  }

  const int fd = ::open(device.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (fd < 0) {
    last_error_ = "open(" + device + ") failed: " + std::strerror(errno);
    return false;
  }

  termios tty{};
  if (tcgetattr(fd, &tty) != 0) {
    last_error_ = "tcgetattr failed: " + std::string(std::strerror(errno));
    ::close(fd);
    return false;
  }

  cfmakeraw(&tty);
  cfsetispeed(&tty, static_cast<speed_t>(speed));
  cfsetospeed(&tty, static_cast<speed_t>(speed));

  tty.c_cflag |= (CLOCAL | CREAD);   // ignore modem lines, enable receiver
  tty.c_cflag &= ~PARENB;            // 8N1: no parity
  tty.c_cflag &= ~CSTOPB;            // one stop bit
  tty.c_cflag &= ~CSIZE;
  tty.c_cflag |= CS8;                // 8 data bits
  tty.c_cflag &= ~CRTSCTS;           // no hardware flow control

  // Non-blocking read: return immediately with whatever is present.
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;

  if (tcsetattr(fd, TCSANOW, &tty) != 0) {
    last_error_ = "tcsetattr failed: " + std::string(std::strerror(errno));
    ::close(fd);
    return false;
  }
  tcflush(fd, TCIOFLUSH);

  fd_ = fd;
  device_ = device;
  last_error_.clear();
  return true;
}

void SerialPort::close()
{
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
}

ReadStatus SerialPort::read(std::vector<uint8_t> & out)
{
  if (fd_ < 0) {
    return ReadStatus::kDisconnected;
  }
  uint8_t chunk[kReadChunk];
  const ssize_t r = ::read(fd_, chunk, sizeof(chunk));
  if (r > 0) {
    out.insert(out.end(), chunk, chunk + r);
    return ReadStatus::kOk;
  }
  if (r == 0) {
    return ReadStatus::kOk;  // nothing available right now
  }
  // r < 0
  if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
    return ReadStatus::kOk;  // transient: no data yet
  }
  last_error_ = "read failed: " + std::string(std::strerror(errno));
  return ReadStatus::kDisconnected;
}

bool SerialPort::write(const uint8_t * data, std::size_t len)
{
  if (fd_ < 0) {
    last_error_ = "write on closed port";
    return false;
  }
  std::size_t written = 0;
  while (written < len) {
    const ssize_t w = ::write(fd_, data + written, len - written);
    if (w > 0) {
      written += static_cast<std::size_t>(w);
      continue;
    }
    if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
      continue;  // retry transient
    }
    last_error_ = "write failed: " + std::string(std::strerror(errno));
    return false;
  }
  return true;
}

}  // namespace ds10_driver
