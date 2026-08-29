package bench;

public record UpdateRequest(String id, String name, long expectedVersion) {}
