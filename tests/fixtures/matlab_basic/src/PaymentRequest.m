classdef PaymentRequest
    properties
        UserId
        Amount
    end
    methods
        function obj = PaymentRequest(userId, amount)
            obj.UserId = userId;
            obj.Amount = amount;
        end
    end
end
