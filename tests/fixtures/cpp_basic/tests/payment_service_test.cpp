#include "acme/payment_service.hpp"

namespace acme {

void authorize_allows_valid_payment() {
  PaymentGateway gateway;
  PaymentService service(&gateway);
  service.authorize(PaymentRequest{42});
}

void authorize_fails_invalid_payment() {
  PaymentGateway gateway;
  PaymentService service(&gateway);
  service.authorize(PaymentRequest{0});
}

}  // namespace acme
