package bench;

public final class WidgetApi {
    private final WidgetService service;

    public WidgetApi(WidgetService service) {
        this.service = service;
    }

    public UpdateResponse update(UpdateRequest request) {
        WidgetService.Result result = service.update(request);
        int status = switch (result.status()) {
            case UPDATED -> 200;
            case BAD_REQUEST -> 400;
            case NOT_FOUND -> 404;
            case CONFLICT -> 409;
        };
        return new UpdateResponse(status, result.widget(), result.error());
    }
}
