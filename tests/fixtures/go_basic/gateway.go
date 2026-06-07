package payments

import "context"

type PaymentGateway interface {
	Charge(ctx context.Context, request PaymentRequest) (Receipt, error)
}
