public final class Events {
    private Events() {}

    public static String encode(String payload) {
        return payload.length() + "#" + payload;
    }

    public static String decode(String record) {
        int delimiter = record.indexOf('#');
        if (delimiter <= 0) throw new IllegalArgumentException("invalid record");
        String prefix = record.substring(0, delimiter);
        if (!prefix.chars().allMatch(Character::isDigit)) {
            throw new IllegalArgumentException("invalid length");
        }
        int length;
        try { length = Integer.parseInt(prefix); }
        catch (NumberFormatException error) { throw new IllegalArgumentException("invalid length", error); }
        String payload = record.substring(delimiter + 1);
        if (payload.length() != length) throw new IllegalArgumentException("length mismatch");
        return payload;
    }
}
