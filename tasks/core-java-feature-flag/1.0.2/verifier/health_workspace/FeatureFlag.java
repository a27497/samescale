public final class FeatureFlag {
    private FeatureFlag() {}

    public interface Repository { String load(String key); }
    public static final class RepositoryException extends RuntimeException {
        public RepositoryException(String message) { super(message); }
    }
    public static final class ServiceException extends RuntimeException {
        public ServiceException(String message, Throwable cause) { super(message, cause); }
    }

    public static String fetch(Repository repository, String key) {
        if (key == null || key.isBlank()) throw new IllegalArgumentException("key is required");
        try { return repository.load(key); }
        catch (RepositoryException error) { throw new ServiceException("load failed", error); }
    }
}
