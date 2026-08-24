public final class FeatureFlag {
    private FeatureFlag() {}

    public interface Repository { String load(String key); }
    public static final class RepositoryException extends RuntimeException {
        public RepositoryException(String message) { super(message); }
    }
    public static final class ServiceException extends RuntimeException {
        public ServiceException(String message) { super(message); }
    }

    public static String fetch(Repository repository, String key) {
        try { return repository.load(key); }
        catch (RuntimeException error) { throw new ServiceException("load failed"); }
    }
}
