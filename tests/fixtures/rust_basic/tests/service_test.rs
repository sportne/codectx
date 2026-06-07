use rust_basic::gateway::Gateway;
use rust_basic::request::PaymentRequest;
use rust_basic::PaymentService;

#[test]
fn authorize_accepts_positive_amount() {
    let service = PaymentService::new(Gateway);
    let request = PaymentRequest::new("req-1".to_string(), 100);

    let receipt = service.authorize(request).expect("receipt");

    assert_eq!(receipt.id, "req-1");
}
