public final class Quota {
    public enum State { NEW, RESERVED, COMMITTED, CANCELLED }
    private State state = State.NEW;
    public State state() { return state; }
    public void reserve() { require(State.NEW); state = State.RESERVED; }
    public void commit() { require(State.RESERVED); state = State.COMMITTED; }
    public void cancel() { require(State.RESERVED); state = State.CANCELLED; }
    private void require(State expected) {
        if (state != expected) throw new IllegalStateException("invalid transition from " + state);
    }
}
