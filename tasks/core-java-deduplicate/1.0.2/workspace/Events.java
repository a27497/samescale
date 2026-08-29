public final class Events {
    private Events() {}

    public static String encode(String payload) {
        return payload.length() + "#" + payload;
    }

    public static String decode(String record) {
        return record.split("#")[1];
    }
}
