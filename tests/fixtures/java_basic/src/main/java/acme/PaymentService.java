package acme;

import java.util.Objects;

public class PaymentService {
  private final PaymentGateway gateway;

  public PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
  }

  public boolean authorize(PaymentRequest request) {
    validate(request);
    return gateway.charge(request);
  }

  private void validate(PaymentRequest request) {
    if (request == null) {
      throw new IllegalArgumentException("request");
    }
    Objects.requireNonNull(request.userId(), "userId");
  }
}
