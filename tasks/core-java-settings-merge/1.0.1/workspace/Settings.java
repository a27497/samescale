import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public final class Settings {
    private Settings() {}
    public static Map<String, String> normalize(Map<String, String> headers) {
        Map<String, String> result = new LinkedHashMap<>();
        headers.forEach((name, value) -> result.put(name.toLowerCase(Locale.ROOT), value.trim()));
        return result;
    }
}
