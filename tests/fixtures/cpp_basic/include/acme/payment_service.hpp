#pragma once

#include "acme/payment_gateway.hpp"

namespace acme {

struct PaymentRequest {
  int amount;
};

class PaymentService {
 public:
  explicit PaymentService(PaymentGateway* gateway);
  bool authorize(const PaymentRequest& request);

 private:
  PaymentGateway* gateway_;
  bool validate(const PaymentRequest& request);
};

}  // namespace acme
