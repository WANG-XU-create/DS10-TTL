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

#ifndef DS10_DRIVER__SERIAL_PORT_HPP_
#define DS10_DRIVER__SERIAL_PORT_HPP_

#include <cstdint>
#include <string>
#include <vector>

namespace ds10_driver
{

/// Outcome of a read attempt, so the reader thread can distinguish "no data
/// yet" (idle poll) from "link is broken, reconnect" without exceptions.
enum class ReadStatus
{
  kOk,          ///< bytes may be present (possibly zero on timeout)
  kDisconnected  ///< fatal I/O error (e.g. USB unplugged); reopen required
};

/// RAII termios wrapper for one serial device. This is the only class that
/// touches the fd. It does 8N1 at a configurable baud, non-blocking-ish reads
/// with a short VTIME timeout, and reports link loss so the node can reconnect.
/// It carries no framing or Modbus logic — just bytes in and out.
class SerialPort
{
public:
  SerialPort() = default;
  ~SerialPort();

  SerialPort(const SerialPort &) = delete;
  SerialPort & operator=(const SerialPort &) = delete;

  /// Open `device` at `baud` (8N1). Returns true on success; on failure
  /// last_error() explains why and is_open() stays false.
  bool open(const std::string & device, int baud);

  /// Close the fd if open. Idempotent.
  void close();

  bool is_open() const {return fd_ >= 0;}

  /// Read whatever is available into `out` (appended). Returns kDisconnected on
  /// a fatal error so the caller drops the port and retries; kOk otherwise
  /// (out may be left unchanged when no bytes arrived within the timeout).
  ReadStatus read(std::vector<uint8_t> & out);

  /// Write all bytes. Returns false on error (caller treats as link loss).
  bool write(const uint8_t * data, std::size_t len);

  const std::string & device() const {return device_;}
  std::string last_error() const {return last_error_;}

private:
  /// Map an integer baud to the matching Bxxxx termios constant, or -1.
  static int baud_constant(int baud);

  int fd_ = -1;
  std::string device_;
  std::string last_error_;
};

}  // namespace ds10_driver

#endif  // DS10_DRIVER__SERIAL_PORT_HPP_
