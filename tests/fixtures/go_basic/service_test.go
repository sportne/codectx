package payments

import "context"

type fakeGateway struct{}

func (fakeGateway) Charge(ctx context.Context, request PaymentRequest) (Receipt, error) {
	return Receipt{Approved: true}, nil
}

func TestAuthorizeAllowsValidPayment() {
	service := NewPaymentService(fakeGateway{})
	service.Authorize(context.Background(), PaymentRequest{UserID: "u1", Amount: 42})
}
