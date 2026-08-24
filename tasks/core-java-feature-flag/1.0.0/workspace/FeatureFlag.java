public final class FeatureFlag {
    private FeatureFlag() {}

    public static boolean parse(String value, boolean defaultValue) {
        return value == null ? false : Boolean.parseBoolean(value);
    }
}
