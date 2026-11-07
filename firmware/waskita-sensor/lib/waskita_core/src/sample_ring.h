// WASKITA - ring buffer FIFO untuk sampel telemetri yang belum terkirim.
// Penyimpanan disediakan pemanggil (malloc saat boot) supaya kapasitas bisa
// diturunkan bila heap tidak cukup. TIDAK thread-safe: hanya dipakai dari
// satu task (loop()).
#pragma once

#include <stddef.h>

#include "power_calc.h"

namespace waskita {

class SampleRing {
 public:
  SampleRing() : buf_(nullptr), cap_(0), head_(0), count_(0) {}

  void attach(TelemetrySample* storage, size_t capacity) {
    buf_ = storage;
    cap_ = storage ? capacity : 0;
    head_ = 0;
    count_ = 0;
  }

  size_t size() const { return count_; }
  size_t capacity() const { return cap_; }
  bool empty() const { return count_ == 0; }
  bool full() const { return cap_ > 0 && count_ == cap_; }

  // Tambah di belakang. Bila penuh, sampel tertua ditimpa: return true dan
  // salinannya ditulis ke *evicted (bila tidak null).
  bool push(const TelemetrySample& s, TelemetrySample* evicted) {
    if (cap_ == 0) {
      if (evicted) *evicted = s;
      return true;
    }
    if (count_ == cap_) {
      if (evicted) *evicted = buf_[head_];
      buf_[head_] = s;
      head_ = (head_ + 1) % cap_;
      return true;
    }
    buf_[(head_ + count_) % cap_] = s;
    ++count_;
    return false;
  }

  // i = 0 -> sampel tertua. Pemanggil wajib memastikan i < size().
  const TelemetrySample& at(size_t i) const { return buf_[(head_ + i) % cap_]; }

  // Buang n sampel tertua; return jumlah yang benar-benar dibuang.
  size_t popFront(size_t n) {
    if (n > count_) n = count_;
    if (cap_ > 0) head_ = (head_ + n) % cap_;
    count_ -= n;
    return n;
  }

  void clear() {
    head_ = 0;
    count_ = 0;
  }

 private:
  TelemetrySample* buf_;
  size_t cap_;
  size_t head_;
  size_t count_;
};

}  // namespace waskita
