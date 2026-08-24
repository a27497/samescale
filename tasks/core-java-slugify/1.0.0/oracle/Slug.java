import java.util.Locale;

public final class Slug {
    private Slug() {}
    public static String slugify(String title) {
        return title.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-").replaceAll("^-|-$", "");
    }
}
