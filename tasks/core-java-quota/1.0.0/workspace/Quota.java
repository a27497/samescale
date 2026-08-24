public final class Quota {
    private int remaining;

    public Quota(int capacity) { this.remaining = capacity; }
    public int remaining() { return remaining; }

    public boolean consume(int units) {
        if (units < remaining) {
            remaining -= units;
            return true;
        }
        remaining -= units;
        return false;
    }
}
