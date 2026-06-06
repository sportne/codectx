from payments.gateway import PaymentGateway
from payments.request import PaymentRequest
from payments.service import PaymentService


def check_authorize_allows_valid_payment():
    service = PaymentService(PaymentGateway())
    assert service.authorize(PaymentRequest("u1", 42))
