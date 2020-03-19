def copy_attributes(from_thing, to_thing, skip=[""], recursive=False):
	"""Copy attributes from one thing to another.
	from_thing: Object to copy values from. (Only if the attribute already exists in to_thing)
	to_thing: Object to copy attributes into (No new attributes are created, only existing are changed).
	skip: List of attribute names in from_thing that should not be attempted to be copied.
	recursive: Copy iterable attributes recursively.
	"""
	
	bad_stuff = skip + ['active', 'bl_rna', 'error_location', 'error_rotation']
	for prop in dir(from_thing):
		if "__" in prop: continue
		if(prop in bad_stuff): continue

		if(hasattr(to_thing, prop)):
			from_value = getattr(from_thing, prop)
			# Iterables should be copied recursively, except str.
			if recursive and type(from_value) not in [str]:
				# NOTE: I think This will infinite loop if a CollectionProperty contains a reference to itself!
				warn = False
				try:
					# Determine if the property is iterable. Otherwise this throws TypeError.
					iter(from_value)

					to_value = getattr(to_thing, prop)
					# The thing we are copying to must therefore be an iterable as well. If this fails though, we should throw a warning.
					warn = True
					iter(to_value)
					count = min(len(to_value), len(from_value))
					for i in range(0, count):
						copy_attributes(from_value[i], to_value[i], skip, recursive)
				except TypeError: # Not iterable.
					if warn:
						print("WARNING: Could not copy attributes from iterable to non-iterable field: " + prop + 
							"\nFrom object: " + str(from_thing) + 
							"\nTo object: " + str(to_thing)
						)

			# Copy the attribute.
			try:
				setattr(to_thing, prop, from_value)
			except AttributeError:	# Read-Only properties.
				continue