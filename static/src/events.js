const handlers = new Map();

export function on(event, fn) {
    if (!handlers.has(event)) {
        handlers.set(event, new Set());
    }
    handlers.get(event).add(fn);
    return () => handlers.get(event).delete(fn);
}

export function emit(event, ...args) {
    const set = handlers.get(event);
    if (set) {
        set.forEach((fn) => fn(...args));
    }
}
