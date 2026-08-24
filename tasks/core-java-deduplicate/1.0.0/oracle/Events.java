import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

public final class Events {
    private Events() {}

    public static List<String> deduplicate(List<String> events) {
        return new ArrayList<>(new LinkedHashSet<>(events));
    }
}
