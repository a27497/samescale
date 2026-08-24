import java.util.Map;

public final class Defaults {
    private Defaults() {}
    public static Map<String, Object> values() {
        return Map.of("timeout", 30, "retries", 2, "region", "local");
    }
}
