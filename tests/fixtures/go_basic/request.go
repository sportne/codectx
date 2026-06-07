package payments

type PaymentRequest struct {
	UserID string
	Amount int
}

type Receipt struct {
	Approved bool
}
