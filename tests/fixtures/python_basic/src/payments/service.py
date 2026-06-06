from payments.gateway import PaymentGateway
from payments.request import PaymentRequest


class PaymentService:
    gateway = None

    def __init__(self, gateway: PaymentGateway):
        self.gateway = gateway

    def authorize(self, request):
        validate(request)
        return self.gateway.charge(request)


def validate(request):
    if request is None:
        raise ValueError("request")
    PaymentRequest(request.user_id, request.amount)
