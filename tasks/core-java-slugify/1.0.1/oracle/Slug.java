import java.util.ArrayList;
import java.util.List;

public final class Slug {
    private Slug() {}
    public static <T> List<List<T>> partition(List<T> values, int size) {
        if (size <= 0) throw new IllegalArgumentException("size must be positive");
        List<List<T>> result = new ArrayList<>();
        for (int index = 0; index < values.size(); index += size) {
            result.add(new ArrayList<>(values.subList(index, Math.min(index + size, values.size()))));
        }
        return result;
    }
}
