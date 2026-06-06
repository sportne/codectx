gateway = PaymentGateway();
request = PaymentRequest("u1", 42);
service = PaymentService(gateway);
ok = service.authorize(request);
