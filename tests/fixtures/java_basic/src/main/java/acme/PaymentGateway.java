package acme;

public class PaymentGateway {
  public boolean charge(PaymentRequest request) {
    return request.amount() > 0;
  }
}
