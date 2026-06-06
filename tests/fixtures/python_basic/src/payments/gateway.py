class PaymentGateway:
    def charge(self, request):
        return request.amount > 0
