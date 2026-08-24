public final class Quota {
    private int remaining;

    public Quota(int capacity) { this.remaining = capacity; }
    public int remaining() { return remaining; }

    public boolean consume(int units) {
        if (units <= 0) throw new IllegalArgumentException("units must be positive");
        if (units > remaining) return false;
        remaining -= units;
        return true;
    }
}
