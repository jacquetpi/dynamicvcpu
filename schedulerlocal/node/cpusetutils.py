def get_cpus_with_weight(cpuset, distance_max, from_list : list, to_list : list, exclude_max : bool = True):
    """Computer the average distance of CPU presents in from_list to the one in to_list
    ----------

    Parameters
    ----------
    from_list : list
        list of ServerCPU
    to_list : list
        list of ServerCPU
    exclude_max : bool (optional)
        Should CPU having a distance value higher than the one fixed in max_distance attribute being disregarded
    
    Returns
    -------
    distance : dict
        Dict of CPUID (as key) with average distance being computed
    """
    computed_distances = dict()
    for available_cpu in from_list:
        total_distance = 0
        total_count = 0

        exclude_identical = False
        for subset_cpu in to_list:
            if subset_cpu == available_cpu: 
                exclude_identical = True
                break

            distance = cpuset.get_distance_between_cpus(subset_cpu, available_cpu)
            if exclude_max and (distance >= distance_max): continue

            total_distance+=distance
            total_count+=1

        if exclude_identical : continue
        if total_count <= 0: computed_distances[available_cpu.get_cpu_id()] = 0
        elif total_distance>=0: computed_distances[available_cpu.get_cpu_id()] = total_distance/total_count

    return computed_distances