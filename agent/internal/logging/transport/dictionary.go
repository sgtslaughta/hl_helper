package transport

import "sync"

type Dictionary struct {
	mu         sync.RWMutex
	forward    map[string]uint32
	reverse    map[uint32]string
	nextID     uint32
	lastDeltaV uint32 // version at which Delta() was last called
}

func New() *Dictionary {
	return &Dictionary{
		forward: make(map[string]uint32),
		reverse: make(map[uint32]string),
	}
}

func (d *Dictionary) Intern(s string) (uint32, bool) {
	d.mu.RLock()
	if id, ok := d.forward[s]; ok {
		d.mu.RUnlock()
		return id, false
	}
	d.mu.RUnlock()

	d.mu.Lock()
	defer d.mu.Unlock()
	if id, ok := d.forward[s]; ok { // double-check after upgrade
		return id, false
	}
	d.nextID++
	id := d.nextID
	d.forward[s] = id
	d.reverse[id] = s
	return id, true
}

func (d *Dictionary) Version() uint32 {
	d.mu.RLock()
	defer d.mu.RUnlock()
	return d.nextID
}

func (d *Dictionary) Snapshot() map[uint32]string {
	d.mu.RLock()
	defer d.mu.RUnlock()
	out := make(map[uint32]string, len(d.reverse))
	for k, v := range d.reverse {
		out[k] = v
	}
	return out
}

func (d *Dictionary) Delta() map[uint32]string {
	d.mu.Lock()
	defer d.mu.Unlock()
	out := make(map[uint32]string)
	for id, s := range d.reverse {
		if id > d.lastDeltaV {
			out[id] = s
		}
	}
	d.lastDeltaV = d.nextID
	return out
}

func (d *Dictionary) Reset() {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.forward = make(map[string]uint32)
	d.reverse = make(map[uint32]string)
	d.nextID = 0
	d.lastDeltaV = 0
}
