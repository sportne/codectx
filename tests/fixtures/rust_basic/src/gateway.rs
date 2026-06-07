pub struct Gateway;

pub struct Receipt {
    pub id: String,
}

impl Gateway {
    pub fn charge(&self, request: crate::request::PaymentRequest) -> Receipt {
        Receipt {
            id: request.id().to_string(),
        }
    }
}
