import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public final class Settings {
    private Settings() {}
    public static Map<String, String> normalize(Map<String, String> headers) {
        Map<String, String> result = new LinkedHashMap<>();
        for (var entry : headers.entrySet()) {
            String rawName = entry.getKey(); String rawValue = entry.getValue();
            if (rawName == null || rawValue == null || Defaults.hasLineBreak(rawName) || Defaults.hasLineBreak(rawValue)) {
                throw new IllegalArgumentException("invalid header");
            }
            String name = rawName.strip().toLowerCase(Locale.ROOT);
            if (name.isEmpty() || result.containsKey(name)) throw new IllegalArgumentException("invalid header name");
            result.put(name, rawValue.strip().replaceAll("[ \\t]+", " "));
        }
        return result;
    }
}
