public final class Quota {
    public enum State { NEW, RESERVED, COMMITTED, CANCELLED }
    private State state = State.NEW;
    public State state() { return state; }
    public void reserve() { state = State.RESERVED; }
    public void commit() { state = State.COMMITTED; }
    public void cancel() { state = State.CANCELLED; }
}
