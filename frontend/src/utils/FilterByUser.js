const filterByUser = (data, user) => {
  // Handle various response shapes: paginated {results: [...]}, plain array [...], or other
  const items = Array.isArray(data?.results)
    ? data.results
    : Array.isArray(data)
      ? data
      : [];

  const filtered = items.filter((item) => {
    if (item?.created_by?.id) {
      return item.created_by.id === Number(user?.user_id);
    }
    if (item?.created_by_username) {
      return item.created_by_username === user?.username;
    }
    return false;
  });

  // Preserve pagination wrapper if present
  return data?.results && Array.isArray(data?.results)
    ? { ...data, results: filtered, count: filtered.length }
    : filtered;
};
export default filterByUser;
