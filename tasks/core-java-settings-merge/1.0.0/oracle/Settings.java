import java.util.HashMap;
import java.util.Map;

public final class Settings {
    private Settings() {}
    public static Map<String, Object> merge(Map<String, Object> overrides) {
        Map<String, Object> merged = new HashMap<>(Defaults.values());
        merged.putAll(overrides);
        return merged;
    }
}
