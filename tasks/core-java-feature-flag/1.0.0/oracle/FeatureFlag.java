import java.util.Locale;
import java.util.Set;

public final class FeatureFlag {
    private static final Set<String> TRUE_VALUES = Set.of("true", "1", "yes", "on");
    private static final Set<String> FALSE_VALUES = Set.of("false", "0", "no", "off");

    private FeatureFlag() {}

    public static boolean parse(String value, boolean defaultValue) {
        if (value == null) return defaultValue;
        String normalized = value.strip().toLowerCase(Locale.ROOT);
        if (TRUE_VALUES.contains(normalized)) return true;
        if (FALSE_VALUES.contains(normalized)) return false;
        throw new IllegalArgumentException("invalid feature flag");
    }
}
