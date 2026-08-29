public final class Defaults {
    private Defaults() {}
    public static boolean hasLineBreak(String value) { return value.contains("\r") || value.contains("\n"); }
}
