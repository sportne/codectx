pub mod gateway;
pub mod request;

use crate::gateway::{Gateway, Receipt};
use crate::request::PaymentRequest;

pub enum PaymentError {
    InvalidAmount,
}

pub trait Authorizer {
    fn authorize(&self, request: PaymentRequest) -> Result<Receipt, PaymentError>;
}

pub struct PaymentService {
    gateway: Gateway,
}

impl PaymentService {
    pub fn new(gateway: Gateway) -> Self {
        Self { gateway }
    }

    pub fn authorize(&self, request: PaymentRequest) -> Result<Receipt, PaymentError> {
        self.validate(&request)?;
        Ok(self.gateway.charge(request))
    }

    fn validate(&self, request: &PaymentRequest) -> Result<(), PaymentError> {
        if request.amount() == 0 {
            return Err(PaymentError::InvalidAmount);
        }
        Ok(())
    }
}
