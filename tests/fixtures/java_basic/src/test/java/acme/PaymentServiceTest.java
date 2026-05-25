package acme;

class PaymentServiceTest {
  void authorize_allows_valid_payment() {
    PaymentService service = new PaymentService(new PaymentGateway());
    service.authorize(new PaymentRequest("u1", 42));
  }

  void authorize_fails_invalid_payment() {
    PaymentService service = new PaymentService(new PaymentGateway());
    service.authorize(null);
  }
}
