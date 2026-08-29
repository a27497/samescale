package bench;

public final class WidgetApi {
    private final WidgetService service;

    public WidgetApi(WidgetService service) {
        this.service = service;
    }

    public UpdateResponse update(UpdateRequest request) {
        WidgetService.Result result = service.update(request);
        return new UpdateResponse(200, result.widget(), result.error());
    }
}
