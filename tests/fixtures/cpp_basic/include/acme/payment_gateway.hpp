#pragma once

#include "acme/payment_service.hpp"

namespace acme {

class PaymentGateway {
 public:
  bool charge(const PaymentRequest& request);
};

}  // namespace acme
