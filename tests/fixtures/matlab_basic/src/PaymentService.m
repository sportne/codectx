classdef PaymentService < handle
    properties
        Gateway
    end
    methods
        function obj = PaymentService(gateway)
            obj.Gateway = gateway;
        end

        function ok = authorize(obj, request)
            validate(request);
            ok = obj.Gateway.charge(request);
        end

        function validate(obj, request)
            if isempty(request)
                error("request");
            end
        end
    end
end
