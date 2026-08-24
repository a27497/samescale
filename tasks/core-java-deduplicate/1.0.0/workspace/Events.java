import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

public final class Events {
    private Events() {}

    public static List<String> deduplicate(List<String> events) {
        return new ArrayList<>(new TreeSet<>(events));
    }
}
