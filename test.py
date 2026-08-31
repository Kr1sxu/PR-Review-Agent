
buns = [5,2,3,1]

def bubble_Sort(nums):
       n = len(buns)

    for i in range(n-1):
             swapped = False


    for j in range(n - 1 -i):
        if nums[j] > nums[j+1]:
            nums[j],nums[j+1] = nums[j+1],nums[j]
            swapped = True



    if not swapped:
          break

return nums