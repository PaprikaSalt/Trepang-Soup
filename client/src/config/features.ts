// Public Web packages exclude administrator UI at route-registration time.
// Desktop builds keep the feature unless explicitly disabled by their environment.
export const adminEnabled = import.meta.env.VITE_ENABLE_ADMIN !== "false";
