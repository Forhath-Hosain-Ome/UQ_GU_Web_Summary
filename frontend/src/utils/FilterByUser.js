// Filter batches/reports to only show items created by the logged-in user
const filterByUser = (data) => {
    const items = data?.results || data || [];
    const filtered = items.filter(item => item.created_by && item.created_by.id === Number(user?.user_id));

    if (data?.results) {
      return { ...data, results: filtered, count: filtered.length };
    }
    return filtered;
};

export default filterByUser;