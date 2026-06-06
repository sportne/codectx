classdef PaymentGateway
    methods
        function ok = charge(obj, request)
            ok = request.Amount > 0;
        end
    end
end
