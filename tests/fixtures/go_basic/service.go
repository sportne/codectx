package payments

import (
	"context"
	"errors"
)

type PaymentService struct {
	Gateway PaymentGateway
}

type Authorizer interface {
	Authorize(ctx context.Context, request PaymentRequest) (Receipt, error)
}

func NewPaymentService(gateway PaymentGateway) *PaymentService {
	return &PaymentService{Gateway: gateway}
}

func (s *PaymentService) Authorize(ctx context.Context, request PaymentRequest) (Receipt, error) {
	if request.Amount <= 0 {
		return Receipt{}, errors.New("request")
	}
	s.validate(request)
	return s.Gateway.Charge(ctx, request)
}

func (s *PaymentService) validate(request PaymentRequest) error {
	if request.UserID == "" {
		return errors.New("user")
	}
	return nil
}
