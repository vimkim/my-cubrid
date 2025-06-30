import argparse
import h5py
import numpy as np

def find_all_zero_rows(hdf5_file, dataset_name):
    zero_indices = []
    with h5py.File(hdf5_file, 'r') as f:
        dset = f[dataset_name]
        batch_size = 1000

        for i in range(0, dset.shape[0], batch_size):
            batch = dset[i : i + batch_size]
            # Boolean mask: True where row is all zeros
            mask = np.all(batch == 0, axis=1)
            found = np.where(mask)[0]
            if found.size > 0:
                # Adjust indices to dataset-global indices
                zero_indices.extend((found + i).tolist())

    return zero_indices

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check if a dataset contains any all-zero vectors and print their indices.")
    parser.add_argument("hdf5_file", help="Path to the HDF5 file")
    parser.add_argument("dataset_name", help="Dataset name (e.g., 'test')")
    parser.add_argument("--column", default="emb", help="Column name (ignored, for compatibility)")

    args = parser.parse_args()

    zero_rows = find_all_zero_rows(args.hdf5_file, args.dataset_name)

    if zero_rows:
        print(f"Found {len(zero_rows)} all-zero vector(s). Row indices:")
        for idx in zero_rows:
            print(f"Row {idx}")
        # print the total number of all-zero vectors
        print(f"Total number of all-zero vectors: {len(zero_rows)}")
    else:
        print("No all-zero vectors found.")
