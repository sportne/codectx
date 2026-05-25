#include "acme/payment_service.hpp"

#include <stdexcept>

namespace acme {

PaymentService::PaymentService(PaymentGateway* gateway) : gateway_(gateway) {}

bool PaymentService::authorize(const PaymentRequest& request) {
  validate(request);
  return gateway_->charge(request);
}

bool PaymentService::validate(const PaymentRequest& request) {
  if (request.amount <= 0) {
    throw std::invalid_argument("amount");
  }
  return true;
}

}  // namespace acme
