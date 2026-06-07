pub struct PaymentRequest {
    id: String,
    amount: u32,
}

impl PaymentRequest {
    pub fn new(id: String, amount: u32) -> Self {
        Self { id, amount }
    }

    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn amount(&self) -> u32 {
        self.amount
    }
}
